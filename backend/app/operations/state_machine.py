"""Workflow and task state machines for P-12 (§5/§6).

Pure module: the transition maps plus validation. The service is the
only writer of workflow/task status; every transition it performs is
checked here first, mirroring the P-01 approvals pattern
(``validate_transition`` raises ``InvalidStateTransitionError``).
"""
from __future__ import annotations

from ..core.exceptions import InvalidStateTransitionError

WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"VALIDATING", "CANCELLED", "ARCHIVED"},
    "VALIDATING": {"DRAFT", "READY", "BLOCKED", "CANCELLED"},
    "READY": {"WAITING_FOR_APPROVAL", "SCHEDULED", "RUNNING",
              "PAUSED", "CANCELLED", "EXPIRED"},
    "WAITING_FOR_APPROVAL": {"READY", "SCHEDULED", "RUNNING",
                             "CANCELLED", "EXPIRED", "BLOCKED"},
    "SCHEDULED": {"RUNNING", "PAUSED", "CANCELLED", "EXPIRED"},
    "RUNNING": {"PAUSED", "BLOCKED", "VERIFYING", "FAILED",
                "CANCELLED", "RECOVERY_PENDING", "WAITING_FOR_APPROVAL",
                "COMPENSATING"},
    "PAUSED": {"RUNNING", "SCHEDULED", "CANCELLED", "BLOCKED"},
    "BLOCKED": {"READY", "RUNNING", "PAUSED", "CANCELLED", "FAILED"},
    "VERIFYING": {"COMPLETED", "FAILED", "RECOVERY_PENDING",
                  "COMPENSATING", "RUNNING"},
    "RECOVERY_PENDING": {"RUNNING", "PAUSED", "FAILED", "CANCELLED",
                         "COMPENSATING"},
    "COMPENSATING": {"FAILED", "COMPLETED", "RECOVERY_PENDING"},
    "COMPLETED": {"ARCHIVED"},
    "FAILED": {"ARCHIVED", "RECOVERY_PENDING"},
    "CANCELLED": {"ARCHIVED"},
    "EXPIRED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

TASK_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"READY", "BLOCKED", "CANCELLED", "SKIPPED", "FAILED",
                "WAITING_FOR_APPROVAL", "RUNNING"},
    "READY": {"WAITING_FOR_APPROVAL", "RUNNING", "BLOCKED",
              "CANCELLED", "SKIPPED", "FAILED"},
    "WAITING_FOR_APPROVAL": {"READY", "RUNNING", "CANCELLED",
                             "BLOCKED", "FAILED"},
    "RUNNING": {"VERIFYING", "COMPLETED", "FAILED", "RECOVERY_PENDING",
                "CANCELLED", "BLOCKED"},
    "VERIFYING": {"COMPLETED", "FAILED", "RECOVERY_PENDING"},
    "BLOCKED": {"PENDING", "READY", "CANCELLED", "SKIPPED", "FAILED"},
    "RECOVERY_PENDING": {"READY", "RUNNING", "DEAD_LETTER",
                         "CANCELLED", "FAILED"},
    "COMPLETED": set(),
    "FAILED": {"RECOVERY_PENDING", "DEAD_LETTER"},
    "DEAD_LETTER": set(),
    "CANCELLED": set(),
    "SKIPPED": set(),
}


def validate_workflow_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = WORKFLOW_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"workflow transition {current} -> {target} is not allowed",
            details={"current": current, "target": target,
                     "allowed": sorted(allowed)})


def validate_task_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = TASK_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStateTransitionError(
            f"workflow task transition {current} -> {target} is not allowed",
            details={"current": current, "target": target,
                     "allowed": sorted(allowed)})
