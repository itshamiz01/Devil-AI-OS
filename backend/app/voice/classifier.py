"""Deterministic classification of an interpreted voice request
(Expansion Feature 3, pack Phase 3).

This is a SCREEN, not an understanding engine. It classifies the
*request text* with word-boundary vocabulary screens for the two
categories the pack singles out as dangerous to get wrong —
financial operations and high-risk/irreversible actions — and
otherwise reads the shape of the plan the existing P-02 planner
actually produced (its tools, levels and permissions). It never
claims the system understood the speaker; when no plan exists and
no screen matches, the honest result is ``unresolved`` and the
command ends at ``needs_clarification``.

A command is CONSEQUENTIAL when:
- its category is ``financial_operation`` or ``high_risk``, or
- any plan step's tool requires approval in the P-02 tool registry
  (level L2+), or
- any plan step's permission is one of P-01's
  approval-required permissions.

Consequential commands never execute from voice alone: they stop
at ``awaiting_confirmation`` for an on-screen owner decision.
"""
from __future__ import annotations

import re

from . import constants as C

# Word-boundary screens. Kept deliberately small and explicit —
# this vocabulary is policy (it decides what needs a human
# confirmation), so it lives in code, not in a model.
_FINANCIAL_RE = re.compile(
    r"\b(transfer|transfers|payment|payments|pay|paid|refund|refunds|"
    r"purchase|purchases|buy|sell|invoice|invoices|wallet|bank|"
    r"money|spend|spending|charge|billing|checkout|withdraw|deposit)\b")
_HIGH_RISK_RE = re.compile(
    r"\b(delete|deletes|erase|remove|destroy|wipe|format|"
    r"shut\s?down|restart|reboot|install|uninstall|publish|"
    r"send|approve|approves|sign|submit)\b")
_QUESTION_RE = re.compile(
    r"(\?|^\s*(what|why|how|when|where|who|which|is|are|do|does|"
    r"can|could|should)\b)")

# Tools whose result is information rather than an action. All
# other registered tools are treated as operations.
_INFORMATION_TOOLS = {"core.health_snapshot"}


def is_stop_phrase(text: str) -> bool:
    """The voice-native stop control: an exact normalised match,
    nothing fuzzier — a stop that triggers on near-misses would
    cancel work the owner did not ask to cancel."""
    normalised = re.sub(r"[\s.!?,;]+$", "", text.strip().lower())
    normalised = re.sub(r"\s+", " ", normalised)
    return normalised in C.STOP_PHRASES


def classify(text: str, plan_steps: list[dict],
             tools) -> tuple[str, str, bool]:
    """Return (category, risk_level, requires_confirmation).

    ``plan_steps`` is a list of {tool_name, permission} dicts (empty
    when no planner could produce a plan); ``tools`` is the P-02
    ToolRegistryView used for approval levels.
    """
    lower = text.lower()
    if _FINANCIAL_RE.search(lower):
        category = C.CAT_FINANCIAL
    elif _HIGH_RISK_RE.search(lower):
        category = C.CAT_HIGH_RISK
    elif plan_steps:
        if all(s["tool_name"] in _INFORMATION_TOOLS for s in plan_steps):
            category = C.CAT_INFORMATION
        else:
            category = C.CAT_SYSTEM_OPERATION
    elif _QUESTION_RE.search(lower):
        category = C.CAT_QUESTION
    else:
        category = C.CAT_UNRESOLVED

    consequential = category in (C.CAT_FINANCIAL, C.CAT_HIGH_RISK)
    if not consequential:
        from ..permissions.policies import APPROVAL_REQUIRED_PERMISSIONS
        for step in plan_steps:
            if tools is not None and tools.requires_approval(step["tool_name"]):
                consequential = True
                break
            if step.get("permission") in APPROVAL_REQUIRED_PERMISSIONS:
                consequential = True
                break
    return (category,
            C.RISK_CONSEQUENTIAL if consequential else C.RISK_LOW,
            consequential)
