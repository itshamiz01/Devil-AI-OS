"""SurvivalService — the P-08 facade.

Owns the owner-governed settings lifecycle (system_config pattern),
the §25.2 business emergency-pause controls (per-business, on top
of P-05's global mode system — P-08 pauses a business, P-05 stops
the world), the P-08 lifecycle overlay and the combined lifecycle
history (P-06 transitions are never duplicated; they are read and
referenced), and the single ``evaluate`` entry point that runs
monitoring checks → health snapshot → monitoring events.
"""
from __future__ import annotations

import json

from ..core.exceptions import (
    NotFoundError, PermissionDeniedError, ValidationError,
)
from ..database.models.survival import (
    BusinessLifecycleOverlay, BusinessPauseControl,
)
from ..database.repositories.survival import (
    LifecycleOverlayRepository, PauseControlRepository,
)
from ..events.events import EventType
from ..permissions.models import PrincipalType
from . import constants as C
from .analyst import SurvivalAnalyst
from .decisions import DecisionService
from .experiments import ExperimentService
from .forecasting import ForecastingService
from .health import HealthService
from .monitoring import MonitoringService
from .portfolio import PortfolioService
from .recovery import RecoveryService
from .scaling import ScalingService


class SurvivalService:
    def __init__(self, session_factory, *, bus, approvals, recorder,
                 business, financial, agents, execution, tasks):
        from ..database.repositories.core import ConfigRepository
        from .recovery import ClosureService
        self._session_factory = session_factory
        self._config_repo = ConfigRepository
        self._bus = bus
        self.monitoring = MonitoringService(
            session_factory, financial, business, self._audit)
        self.health = HealthService(
            session_factory, self.monitoring, business,
            self.get_settings, self._audit)
        self.decisions = DecisionService(
            session_factory, approvals, recorder, self._audit,
            self.is_paused)
        self.experiments = ExperimentService(
            session_factory, financial, business, approvals,
            self._audit, self.is_paused)
        self.scaling = ScalingService(
            session_factory, financial, business, self.monitoring,
            self.health, self.get_settings, self._audit,
            approvals=approvals)
        self.recovery = RecoveryService(
            session_factory, financial, business, self.monitoring,
            self._audit)
        self.closure = ClosureService(
            session_factory, financial, business, approvals,
            self._audit)
        self.portfolio = PortfolioService(
            session_factory, financial, business, self.monitoring,
            self.health, agents, tasks, self.get_settings, self._audit)
        self.forecasting = ForecastingService(
            session_factory, financial, self.monitoring, self._audit)
        self.analyst = SurvivalAnalyst(
            self.monitoring, self.health, self.portfolio, business)
        self._business = business
        self._financial = financial
        self._seed_settings()

    # ------------------------------------------------------------ settings
    def _seed_settings(self) -> None:
        session = self._session_factory()
        try:
            repo = self._config_repo(session)
            if repo.get(C.SETTINGS_KEY) is None:
                repo.set(C.SETTINGS_KEY, json.dumps(C.DEFAULT_SETTINGS),
                         "survival settings (owner-governed; weights, "
                         "bands, caps and resource limits)")
        finally:
            session.close()

    def get_settings(self) -> dict:
        session = self._session_factory()
        try:
            row = self._config_repo(session).get(C.SETTINGS_KEY)
            raw = row.value if row is not None else None
        finally:
            session.close()
        merged = dict(C.DEFAULT_SETTINGS)
        if raw:
            try:
                merged.update(json.loads(raw))
            except ValueError:
                pass
        return merged

    def update_settings(self, principal, patch: dict) -> dict:
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "survival settings are owner-governed (Article 0): "
                "weights, thresholds and caps cannot be changed by "
                "agents")
        current = self.get_settings()
        for key, value in (patch or {}).items():
            if key == "health_weights":
                if not isinstance(value, dict) or not value or \
                        any(v <= 0 for v in value.values()):
                    raise ValidationError(
                        "health weights must be positive numbers")
                current["health_weights"] = value
            elif key in ("health_bands", "scaling_criteria"):
                if not isinstance(value, dict):
                    raise ValidationError(f"{key} must be an object")
                current[key] = value
            elif key in ("max_increment_ratio",
                         "max_business_capital_share",
                         "concentration_threshold"):
                from decimal import Decimal
                try:
                    number = Decimal(str(value))
                except Exception as exc:
                    raise ValidationError(
                        f"{key} must be a positive number") from exc
                if number <= 0 or number >= 1 and key != \
                        "max_increment_ratio":
                    raise ValidationError(f"{key} must be in (0, 1)")
                if key == "max_increment_ratio" and number <= 0:
                    raise ValidationError(
                        "max_increment_ratio must be positive")
                current[key] = str(value)
            elif key in ("max_concurrent_agents", "inference_slots"):
                if int(value) <= 0:
                    raise ValidationError(f"{key} must be positive")
                current[key] = int(value)
            else:
                raise ValidationError(f"unknown survival setting {key!r}")
        session = self._session_factory()
        try:
            self._config_repo(session).set(
                C.SETTINGS_KEY, json.dumps(current),
                "survival settings updated by owner")
        finally:
            session.close()
        self._audit(principal, "survival.settings_updated", "system",
                    None, "allow", "owner updated survival settings")
        return current

    # ------------------------------------------------------ access mirror
    def business_access_check(self, principal, business_id: str) -> None:
        """Mirror of P-07's assert_business_access (§23): owner and
        system unrestricted; an agent only reaches the business it
        is registered to (its Agent row's business_ref); everyone
        else is denied."""
        if principal.type in (PrincipalType.OWNER, PrincipalType.SYSTEM):
            return
        if principal.type is PrincipalType.AGENT:
            from ..database.models.core import Agent as AgentRow
            session = self._session_factory()
            try:
                agent = session.get(AgentRow, principal.id)
                if agent is not None and \
                        agent.business_ref == business_id:
                    return
            finally:
                session.close()
        raise PermissionDeniedError(
            "survival data for this business is not accessible to "
            "this principal (§23 business-level permissions)")

    # --------------------------------------------------- pause-privates
    def _pause_row(self, business_id: str) -> BusinessPauseControl | None:
        session = self._session_factory()
        try:
            return PauseControlRepository(session).active_for(business_id)
        finally:
            session.close()

    def is_paused(self, business_id: str) -> bool:
        return self._pause_row(business_id) is not None

    # ------------------------------------------------------- pause API
    def pause_business(self, principal, business_id: str,
                       reason: str = "") -> dict:
        self._business.get_business(business_id)
        existing = self._pause_row(business_id)
        if existing is not None:
            return {"business_id": business_id, "state": "PAUSED",
                    "reason": existing.reason,
                    "set_at": existing.created_at.isoformat(),
                    "already_paused": True,
                    "effect": "new controlled execution for this "
                              "business is blocked (§25.2)"}
        session = self._session_factory()
        try:
            row = PauseControlRepository(session).add(
                BusinessPauseControl(
                    business_id=business_id, kind="emergency",
                    active=True, reason=reason or "emergency pause",
                    trigger=_actor(principal),
                    created_by=_actor(principal)))
            result = {"business_id": row.business_id,
                      "state": "PAUSED", "reason": row.reason,
                      "set_by": row.trigger,
                      "set_at": row.created_at.isoformat(),
                      "effect": "new controlled execution, decision "
                                "execution, scaling and experiment "
                                "spend for this business are blocked; "
                                "records, obligations and history are "
                                "preserved (§25.2)"}
        finally:
            session.close()
        self._events_emit(
            principal, EventType.SURVIVAL_BUSINESS_PAUSED, business_id,
            "critical", {"reason": reason, "by": _actor(principal)})
        self._audit(principal, "survival.business_paused", "business",
                    business_id, "allow", reason)
        return result

    def resume_business(self, principal, business_id: str) -> dict:
        if principal.type is not PrincipalType.OWNER:
            raise PermissionDeniedError(
                "lifting an emergency pause requires owner "
                "authorisation (§25.2)")
        self._business.get_business(business_id)
        session = self._session_factory()
        try:
            repo = PauseControlRepository(session)
            row = repo.active_for(business_id)
            if row is not None:
                row.active = False
                row.lifted_by = _actor(principal)
                repo.save(row)
            result = {"business_id": business_id, "state": "ACTIVE",
                      "set_at": (row.updated_at.isoformat() if row
                                 else None)}
        finally:
            session.close()
        self._events_emit(
            principal, EventType.SURVIVAL_BUSINESS_RESUMED, business_id,
            "high", {"by": _actor(principal)})
        self._audit(principal, "survival.business_resumed", "business",
                    business_id, "allow", "owner lifted the pause")
        return result

    def pause_status(self, business_id: str) -> dict:
        row = self._pause_row(business_id)
        if row is None:
            return {"business_id": business_id, "state": "ACTIVE",
                    "reason": None, "set_by": None, "set_at": None}
        return {"business_id": row.business_id, "state": "PAUSED",
                "reason": row.reason, "set_by": row.trigger,
                "set_at": row.created_at.isoformat()}

    # ------------------------------------------------------- lifecycle
    def lifecycle(self, business_id: str) -> dict:
        """Combined lifecycle view: the P-06 state (authoritative)
        + the current P-08 overlay reading. No second state machine
        is stored as truth — the overlay is a snapshot reading."""
        business = self._business.get_business(business_id)
        snapshot = self.health.latest_snapshot(business_id)
        overlay = (snapshot or {}).get("overlay_state") \
            or C.P06_TO_OVERLAY.get(business["status"],
                                    "EARLY_OPERATIONS")
        return {
            "business_id": business_id,
            "p06_state": business["status"],
            "overlay_state": overlay,
            "overlay_source": "p08 health snapshot" if snapshot
                              else "p06 state mapping (no snapshot "
                                   "yet)",
            "paused": self.is_paused(business_id),
            "note": "P-06 owns the lifecycle state machine (§5.1); "
                    "the P-08 overlay is a health/operational "
                    "reading recorded on snapshots",
        }

    def lifecycle_history(self, business_id: str, *, limit: int = 100,
                          offset: int = 0):
        """P-06 transitions (read, never duplicated) + P-08 overlay
        records, merged by time."""
        _events, p06_total = self._business.lifecycle_events(
            business_id, limit=1000, offset=0)
        session = self._session_factory()
        try:
            overlays, overlay_total = LifecycleOverlayRepository(
                session).list_for(business_id, limit=1000, offset=0)
            overlay_rows = [{
                "kind": "p08_overlay", "id": r.id,
                "from_state": r.from_state, "to_state": r.to_state,
                "reason": r.reason,
                "snapshot_id": r.snapshot_id,
                "decision_id": r.decision_id,
                "created_at": r.created_at.isoformat(),
            } for r in overlays]
        finally:
            session.close()
        p06_rows = [{"kind": "p06_transition", **event}
                    for event in _events]
        merged = sorted(p06_rows + overlay_rows,
                        key=lambda row: row.get("created_at") or "")
        page = merged[offset:offset + limit]
        return page, p06_total + overlay_total

    def record_overlay(self, principal, business_id: str,
                       data: dict) -> dict:
        """Record an overlay transition reading. VALIDATING etc.
        are readings; the P-06 machine is only moved through P-06's
        own validated transitions (executed here for PAUSE/ARCHIVE
        flows by the closure path, not by free-form calls)."""
        self._business.get_business(business_id)
        to_state = data.get("to_state")
        if to_state not in C.OVERLAY_STATES:
            raise ValidationError(f"unknown overlay state {to_state!r}")
        if to_state == "SCALING":
            raise PermissionDeniedError(
                "SCALING cannot be recorded directly: it requires a "
                "scaling assessment, an incremental plan and the "
                "§10 approval flow")
        current = self.lifecycle(business_id)["overlay_state"]
        allowed = C.OVERLAY_TRANSITIONS.get(current, set())
        if to_state not in allowed:
            raise ValidationError(
                f"overlay transition {current} -> {to_state} is not "
                f"allowed; permitted: {sorted(allowed)} (§5.3)")
        snapshot = self.health.latest_snapshot(business_id)
        if to_state == "GROWING":
            indicators = (snapshot or {}).get("indicators") or {}
            if not indicators.get("verified_collected_revenue_minor"):
                raise PermissionDeniedError(
                    "GROWING requires verified collected revenue from "
                    "P-07 (§5.2); vanity evidence cannot move a "
                    "business to GROWING")
        session = self._session_factory()
        try:
            row = LifecycleOverlayRepository(session).add(
                BusinessLifecycleOverlay(
                    business_id=business_id, from_state=current,
                    to_state=to_state,
                    reason=data.get("reason") or "",
                    snapshot_id=(snapshot or {}).get("id"),
                    decision_id=data.get("decision_id"),
                    created_by=_actor(principal)))
            result = {"id": row.id, "business_id": business_id,
                      "from_state": row.from_state,
                      "to_state": row.to_state,
                      "reason": row.reason,
                      "created_at": row.created_at.isoformat()}
        finally:
            session.close()
        self._audit(principal, "survival.overlay_recorded", "business",
                    business_id, "allow", f"{current} -> {to_state}")
        return result

    # ---------------------------------------------------------- evaluate
    def _overlay_for(self, business: dict, snapshot: dict) -> str:
        """The overlay reading for a fresh snapshot (§5.1 mapping):
        pre-operational businesses mirror their P-06 state; for an
        OPERATIONAL business the overlay follows the health
        classification and the verified-revenue evidence — GROWING
        requires verified collected revenue in at least two
        snapshots plus a HEALTHY-or-better classification, and is
        never assigned on vanity evidence."""
        status = business["status"]
        if status != "OPERATIONAL":
            return C.P06_TO_OVERLAY.get(status, "EARLY_OPERATIONS")
        classification = snapshot["classification"]
        if classification in ("AT_RISK", "CRITICAL"):
            return "AT_RISK"
        indicators = snapshot.get("indicators") or {}
        revenue = indicators.get("verified_collected_revenue_minor") or 0
        if revenue > 0:
            if classification in ("HEALTHY", "EXCELLENT") and \
                    self.health.snapshots_with_revenue(
                        business["id"]) >= 2:
                return "GROWING"
            if classification in ("STABLE", "HEALTHY", "EXCELLENT"):
                return "STABLE"
        return "EARLY_OPERATIONS"

    def evaluate(self, principal, business_id: str) -> dict:
        """One bounded evaluation pass (§6.3): collect P-07 readings
        → monitoring checks (against the previous snapshot's
        readings) → health snapshot with the overlay refined by the
        facade. No polling daemon; this runs on demand / on
        recorded source events."""
        from ..database.repositories.survival import (
            HealthSnapshotRepository,
        )
        business = self._business.get_business(business_id)
        previous = self.health.latest_snapshot(business_id)
        reading = self.monitoring.collect(business_id)
        checks = self.monitoring.run_checks(
            principal, business_id,
            (previous or {}).get("indicators"))
        snapshot = self.health.evaluate(
            principal, business_id, reading, self.is_paused(business_id))
        overlay = self._overlay_for(business, snapshot)
        if snapshot["overlay_state"] != overlay:
            session = self._session_factory()
            try:
                repo = HealthSnapshotRepository(session)
                row = repo.get(snapshot["id"])
                if row is not None:
                    row.overlay_state = overlay
                    repo.save(row)
            finally:
                session.close()
            snapshot = self.health.get_snapshot(snapshot["id"])
        return {"business_id": business_id, "checks": checks,
                "snapshot": snapshot,
                "lifecycle": self.lifecycle(business_id)}

    def list_scaling_assessments(self, *, business_id: str | None = None,
                                 limit: int = 50, offset: int = 0):
        from ..database.repositories.survival import (
            ScalingAssessmentRepository,
        )
        from .scaling import assessment_dict
        session = self._session_factory()
        try:
            rows, total = ScalingAssessmentRepository(session).list(
                limit=limit, offset=offset, business_id=business_id)
            return [assessment_dict(r) for r in rows], total
        finally:
            session.close()

    def recovery_plan_business(self, plan_id: str) -> str:
        from ..database.repositories.survival import (
            RecoveryPlanRepository,
        )
        session = self._session_factory()
        try:
            row = RecoveryPlanRepository(session).get(plan_id)
            if row is None:
                raise NotFoundError(
                    f"recovery plan {plan_id} not found")
            return row.business_id
        finally:
            session.close()

    # ------------------------------------------------------------- status
    def status(self) -> dict:
        settings = self.get_settings()
        return {
            "engine": "survival_and_scaling", "phase": "P-08",
            "financial_source": "p07 only (§6.1/§32 rule 3)",
            "lifecycle_owner": "p06 (§5.1)",
            "classifications": C.CLASSIFICATIONS,
            "dimensions": C.DIMENSIONS,
            "overlay_states": C.OVERLAY_STATES,
            "autonomy_levels": {
                "0": "autonomous low-risk routine",
                "1": "reversible operational, no owner approval",
                "2": "moderate, owner configurable",
                "3": "major — owner approval required",
                "4": "owner-only; no agent path exists",
            },
            "settings": settings,
            "monitoring": "event-driven + on-demand evaluation; "
                          "no polling daemon (§6.3)",
            "analyst": "deterministic structured interface (P-02 "
                       "pattern); natural-language layer NOT "
                       "IMPLEMENTED",
            "frontend": "NOT IMPLEMENTED — API only; P-11 owns the "
                        "Command Center (§24)",
        }

    # -------------------------------------------------------------- audit
    def _events_emit(self, principal, event_type, business_id: str,
                     severity: str, payload: dict) -> None:
        """Owner-visible system event via the P-01 event bus
        (fire-and-forget from sync code, the bus's own pattern)."""
        if self._bus is None:
            return
        from ..events.events import Event
        self._bus.publish_sync_safe(Event(
            event_type=event_type, source="survival-engine",
            payload={"business_id": business_id, **payload},
            severity=severity))

    def _audit(self, principal, action: str, resource_type: str,
               resource_id, decision: str, reason: str) -> None:
        """Append to the P-01 audit trail (same pattern as P-07)."""
        from ..database.models.base import utcnow
        from ..database.models.core import AuditEvent
        from ..database.repositories.core import AuditRepository
        session = self._session_factory()
        try:
            AuditRepository(session).add(AuditEvent(
                actor_type=principal.type.value if principal
                else "system",
                actor_id=principal.id if principal else "survival-engine",
                action=action, target_type=resource_type,
                target_id=resource_id, decision=decision,
                reason=reason, details={}, created_at=utcnow()))
        finally:
            session.close()


def _actor(principal) -> str:
    return f"{principal.type.value}:{principal.id}" if principal else "system"
