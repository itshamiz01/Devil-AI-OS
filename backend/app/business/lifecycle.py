"""Business lifecycle state machine (§19).

The distinctions are enforced here and in the service guards, not in
labels: BLUEPRINT_READY does not mean a product exists; generated does
not mean tested; local does not mean deployed; deployed does not mean
publicly available; OPERATIONAL asserts nothing about customers or
revenue (and in staging is reached only as a labelled demonstration
over a local package).
"""
from __future__ import annotations

STATES = [
    "PROPOSED", "ELIGIBILITY_REVIEW", "BLUEPRINTING", "BLUEPRINT_READY",
    "APPROVAL_PENDING", "PRODUCT_PLANNING", "IN_DEVELOPMENT",
    "INTERNAL_TESTING", "DISTRIBUTION_PREPARATION", "LAUNCH_REVIEW",
    "READY_FOR_LAUNCH", "LAUNCH_APPROVAL_PENDING", "LAUNCHING",
    "OPERATIONAL", "PAUSED", "BLOCKED", "FAILED", "ARCHIVED",
]

# Validated transitions (§19). PAUSED may be entered from any active
# working state and returns only to the state it was entered from
# (recorded on the business row as paused_from; enforced by the service).
TRANSITIONS: dict[str, set[str]] = {
    "PROPOSED": {"ELIGIBILITY_REVIEW", "BLOCKED", "FAILED", "ARCHIVED"},
    "ELIGIBILITY_REVIEW": {"BLUEPRINTING", "BLOCKED", "FAILED", "ARCHIVED"},
    "BLUEPRINTING": {"BLUEPRINT_READY", "BLOCKED", "FAILED"},
    "BLUEPRINT_READY": {"APPROVAL_PENDING", "PRODUCT_PLANNING", "BLOCKED", "FAILED"},
    "APPROVAL_PENDING": {"PRODUCT_PLANNING", "BLUEPRINT_READY", "BLOCKED", "FAILED"},
    "PRODUCT_PLANNING": {"IN_DEVELOPMENT", "BLOCKED", "FAILED"},
    "IN_DEVELOPMENT": {"INTERNAL_TESTING", "BLOCKED", "FAILED"},
    "INTERNAL_TESTING": {"DISTRIBUTION_PREPARATION", "IN_DEVELOPMENT",
                          "BLOCKED", "FAILED"},
    "DISTRIBUTION_PREPARATION": {"LAUNCH_REVIEW", "BLOCKED", "FAILED"},
    "LAUNCH_REVIEW": {"READY_FOR_LAUNCH", "DISTRIBUTION_PREPARATION",
                      "BLOCKED", "FAILED"},
    "READY_FOR_LAUNCH": {"LAUNCH_APPROVAL_PENDING", "BLOCKED", "FAILED"},
    "LAUNCH_APPROVAL_PENDING": {"LAUNCHING", "READY_FOR_LAUNCH",
                                "BLOCKED", "FAILED"},
    "LAUNCHING": {"OPERATIONAL", "FAILED"},
    "OPERATIONAL": {"ARCHIVED"},
    "PAUSED": set(),  # resolved dynamically from paused_from
    "BLOCKED": {"ARCHIVED", "FAILED"},
    "FAILED": {"ARCHIVED"},
    "ARCHIVED": set(),
}

PAUSABLE = {
    "ELIGIBILITY_REVIEW", "BLUEPRINTING", "BLUEPRINT_READY",
    "APPROVAL_PENDING", "PRODUCT_PLANNING", "IN_DEVELOPMENT",
    "INTERNAL_TESTING", "DISTRIBUTION_PREPARATION", "LAUNCH_REVIEW",
    "READY_FOR_LAUNCH", "LAUNCH_APPROVAL_PENDING",
}

TERMINAL = {"FAILED", "ARCHIVED"}


def can_transition(current: str, target: str, *, paused_from: str | None = None) -> bool:
    if target == "PAUSED":
        return current in PAUSABLE
    if current == "PAUSED":
        return paused_from is not None and target == paused_from
    return target in TRANSITIONS.get(current, set())
