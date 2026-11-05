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
    # P-04 Dynamic Agent Factory, Stage 3. A template governs what an agent may
    # be, so its creation, revision, verdict, publication and withdrawal are all
    # governance-relevant state changes and travel the same auditable bus. A
    # negative verdict is published too: "this template was refused, and why" is
    # exactly the record an owner needs after the fact.
    "AgentTemplateCreated","AgentTemplateRevised","AgentTemplateValidated",
    "AgentTemplatePublished","AgentTemplateDeprecated","AgentTemplateRestored",
    # P-04 Dynamic Agent Factory, Stage 4. Creating an agent mints an identity,
    # so the request, the decision and its outcome are all published. A rejection
    # and a queued request are published for the same reason a refused approval
    # is: the record of what the system decided *not* to do is what an owner
    # audits afterwards. REUSE_EXISTING emits only AgentCreationRequested -
    # reusing an agent creates nothing, and a creation event for it would inflate
    # every downstream count of agents that were made.
    "AgentCreationRequested","AgentCreated","AgentCreationQueued",
    "AgentCreationApprovalRequested","AgentCreationRejected",
    # P-04 Dynamic Agent Factory, Stage 5. Authority changing hands is the most
    # governance-relevant thing an agent system does, so grants, refusals and
    # revocations are all published. A *denied* capability is published for the
    # same reason a refused approval is: an attempt to widen authority that did
    # not succeed is exactly what an owner wants to see afterwards.
    # CapabilityCatalogChanged is published only when a reconciliation actually
    # changed something, so a normal startup stays quiet.
    "AgentCapabilityGranted","AgentCapabilityRevoked","AgentCapabilityDenied",
    "AgentAssignmentChanged",
    "AgentCapabilityApprovalRequested","CapabilityCatalogChanged",
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
