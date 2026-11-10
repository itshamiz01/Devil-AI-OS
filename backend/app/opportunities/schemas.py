"""Internal schemas for P-03 (task payloads, research-stage IO)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchTaskPayload(BaseModel):
    """Payload of the ``opportunity.research`` P-01 task handler. A task
    carries only a session id — never code, never a URL to fetch directly;
    what gets fetched is decided by the registered-source catalogue."""

    session_id: str = Field(min_length=1, max_length=64)


def capability_assessment(required: list[str], available: list[str]) -> dict:
    required = list(dict.fromkeys(required or []))
    available_set = set(available or [])
    missing = [c for c in required if c not in available_set]
    coverage = (len(required) - len(missing)) / len(required) if required else None
    return {
        "required": required,
        "available": [c for c in required if c in available_set],
        "missing": missing,
        "coverage": coverage,
    }
