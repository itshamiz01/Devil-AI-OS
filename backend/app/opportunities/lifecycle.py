"""Opportunity lifecycle state machine (P-03 §17).

States and permitted transitions are data, validated on every change.
Terminal-ish outcomes (REJECTED, INCOMPATIBLE, BLOCKED_BY_COMPLIANCE,
DUPLICATE) can only move to ARCHIVED (or back to RESEARCHING from
NEEDS_MORE_EVIDENCE / OUTDATED when genuinely new evidence arrives —
"an opportunity may return to research if new evidence becomes available").
"""
from __future__ import annotations

STATES = [
    "DISCOVERED", "INITIAL_SCREENING", "RESEARCHING", "EVIDENCE_REVIEW",
    "COMMERCIAL_ANALYSIS", "VALIDATION_PENDING", "VALIDATED", "RECOMMENDED",
    "NEEDS_MORE_EVIDENCE", "REJECTED", "INCOMPATIBLE",
    "BLOCKED_BY_COMPLIANCE", "DUPLICATE", "OUTDATED", "ARCHIVED",
]

TRANSITIONS: dict[str, set[str]] = {
    "DISCOVERED": {"INITIAL_SCREENING", "DUPLICATE", "ARCHIVED"},
    "INITIAL_SCREENING": {
        "RESEARCHING", "REJECTED", "INCOMPATIBLE", "BLOCKED_BY_COMPLIANCE",
        "DUPLICATE", "NEEDS_MORE_EVIDENCE", "ARCHIVED",
    },
    "RESEARCHING": {
        "EVIDENCE_REVIEW", "NEEDS_MORE_EVIDENCE", "BLOCKED_BY_COMPLIANCE", "ARCHIVED",
    },
    "EVIDENCE_REVIEW": {
        "COMMERCIAL_ANALYSIS", "NEEDS_MORE_EVIDENCE", "RESEARCHING",
        "REJECTED", "BLOCKED_BY_COMPLIANCE", "ARCHIVED",
    },
    "COMMERCIAL_ANALYSIS": {
        "VALIDATION_PENDING", "INCOMPATIBLE", "NEEDS_MORE_EVIDENCE",
        "REJECTED", "BLOCKED_BY_COMPLIANCE", "ARCHIVED",
    },
    "VALIDATION_PENDING": {
        "VALIDATED", "NEEDS_MORE_EVIDENCE", "REJECTED",
        "BLOCKED_BY_COMPLIANCE", "ARCHIVED",
    },
    "VALIDATED": {"RECOMMENDED", "OUTDATED", "BLOCKED_BY_COMPLIANCE", "ARCHIVED"},
    "RECOMMENDED": {"OUTDATED", "ARCHIVED"},
    "NEEDS_MORE_EVIDENCE": {"RESEARCHING", "REJECTED", "ARCHIVED"},
    "REJECTED": {"ARCHIVED"},
    "INCOMPATIBLE": {"ARCHIVED"},
    "BLOCKED_BY_COMPLIANCE": {"ARCHIVED"},
    "DUPLICATE": {"ARCHIVED"},
    "OUTDATED": {"RESEARCHING", "ARCHIVED"},
    "ARCHIVED": set(),
}

# The happy-path pipeline order, for reporting.
PIPELINE = [
    "DISCOVERED", "INITIAL_SCREENING", "RESEARCHING", "EVIDENCE_REVIEW",
    "COMMERCIAL_ANALYSIS", "VALIDATION_PENDING", "VALIDATED", "RECOMMENDED",
]


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def slugify_opportunity(name: str, category: str, geography: str) -> str:
    """Normalised duplicate-detection key (§5, §28.1): case/punctuation
    variants of the same name in the same category+geography collide."""
    import re

    normalised = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"{normalised}|{category}|{(geography or 'global').lower()}"
