from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

EVENT_TYPES = {
    "ApplicationStarted","ApplicationReady","ApplicationStopping","ApplicationStopped",
    "TaskCreated","TaskQueued","TaskStarted","TaskProgressUpdated","TaskCompleted","TaskFailed","TaskCancelled",
    "ApprovalRequested","ApprovalGranted","ApprovalRejected","PermissionDenied","SystemWarning","SystemError",
    "DatabaseUnavailable","ResourceThresholdExceeded",
    # P-01 extension beyond the §8 initial list: the emergency stop is a
    # security-critical state change, so it must be observable and auditable
    # through the same bus as everything else. See ADR-0013.
    "EmergencyActivated","EmergencyDeactivated",
    # P-02 Master Intelligence Engine. These are security- and governance-relevant
    # state changes, so they travel the same auditable bus as everything else
    # rather than living only in engine memory. See ADR-0015.
    "MissionCreated","MissionStateChanged","PlanGenerated","PlanRevised","PlanRejected",
    "TaskDispatched","DecisionRecorded","ModelUnavailable","PromptInjectionDetected",
    "AutonomyLevelChanged",
    # P-03 Opportunity Discovery Engine. An opportunity being rejected is as
    # auditable an outcome as one being recommended - arguably more so, since the
    # phase brief's design goal is that the system must be better at rejecting bad
    # opportunities than at generating attractive ones. Source refusals and
    # governance violations travel the same bus for the same reason: an absence of
    # evidence, and an attempt to exceed authority, are both things the owner needs
    # to be able to see after the fact.
    "OpportunityDiscovered","OpportunityOpened","OpportunityStateChanged",
    "OpportunityRejected","OpportunityRecommended","ResearchSweepCompleted",
    "SourceRefused","EvidenceRecorded","ComplianceBlocked","GovernanceViolation",
}


class Event(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    correlation_id: str | None = None
    task_id: str | None = None
    severity: str = "info"
    payload: dict[str, Any] = Field(default_factory=dict)
