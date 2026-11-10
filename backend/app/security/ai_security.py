"""AI security and prompt-injection defense (§14).

The intelligence layer processes websites, documents, emails, code,
research results, retrieved memories and other agents' outputs —
any of which can carry malicious instructions. This module is the
deterministic screening surface:

- a **trust hierarchy** (§14.1): every content source is classified,
  and lower-authority content can never override higher-authority
  instructions — as a data property, not a model judgement;
- **injection screening** (§14.2): deterministic pattern detection
  returning pattern NAMES only. Screening classifies content as
  data; it is one layer — the structural defence is that no code
  path exists from screened content to policy, permissions,
  approvals or secrets (the Article-0 tests prove that property);
- **outbound secret screening** (§9.3/§14): reuses P-09's secret
  patterns (imported, not duplicated) to stop a secret-shaped value
  leaving in a prompt or report;
- **handoff validation** (§14.4): agent-to-agent messages must be
  structured envelopes; a handoff can request, never grant — the
  receiving side re-verifies through the broker.

No function here asks a model anything (§14.6).
"""
from __future__ import annotations

import re

from ..memory.policy import detect_secrets  # P-09 patterns, reused (§2 rule 6)

# §14.1 trust hierarchy: lower number = higher authority. Content
# may inform decisions at its own level; it may never instruct a
# higher level.
TRUST_LEVELS: dict[str, int] = {
    "owner_constitution": 0,
    "system_policy": 1,
    "authorized_task_instruction": 2,
    "agent_output": 3,
    "external_content": 4,
    "tool_output": 5,
}

# Sources an agent will actually ingest map to the two lowest
# authority levels by default.
SOURCE_TRUST: dict[str, int] = {
    "website": TRUST_LEVELS["external_content"],
    "document": TRUST_LEVELS["external_content"],
    "email": TRUST_LEVELS["external_content"],
    "research_result": TRUST_LEVELS["external_content"],
    "retrieved_memory": TRUST_LEVELS["external_content"],
    "code_comment": TRUST_LEVELS["tool_output"],
    "tool_output": TRUST_LEVELS["tool_output"],
    "agent_message": TRUST_LEVELS["agent_output"],
    "owner_instruction": TRUST_LEVELS["authorized_task_instruction"],
}

INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("policy_override_instruction", re.compile(
        r"(?i)\b(ignore|disregard|override|forget)\b.{0,50}\b(previous|prior|system|security|owner)\b.{0,30}\b(instruction|policy|rule|prompt)")),
    ("security_disable_request", re.compile(
        r"(?i)\b(disable|turn off|remove|bypass)\b.{0,40}\b(security|approval|permission|audit|protection|guard)")),
    ("credential_request", re.compile(
        r"(?i)\b(reveal|show|print|send|give|disclose|leak)\b.{0,40}\b(password|api[_ ]?key|secret|credential|token|private key)")),
    ("secret_exfiltration_request", re.compile(
        r"(?i)\b(send|post|upload|forward)\b.{0,50}\b(credential|api[_ ]?key|secret|\.env|config file)")),
    ("fake_owner_approval", re.compile(
        r"(?i)\b(owner|admin|the user)\b.{0,30}\b(has |have )?(already )?(approved|authorised|authorized|confirmed)\b.{0,40}\b(payment|transfer|transaction|this|it)\b")),
    ("permission_grant_claim", re.compile(
        r"(?i)\b(you (now )?have|i (hereby )?grant|granting)\b.{0,40}\b(permission|access|admin|owner)")),
    ("system_prompt_extraction", re.compile(
        r"(?i)\b(repeat|print|show|reveal)\b.{0,40}\b(system prompt|your instructions|initial prompt)")),
    ("new_instruction_claim", re.compile(
        r"(?i)\b(new|updated|revised)\s+(system\s+)?(instruction|directive|policy)\s*:")),
]


def trust_level_for_source(source: str) -> int:
    """Unknown sources get the LOWEST authority (fail closed)."""
    return SOURCE_TRUST.get(source, TRUST_LEVELS["tool_output"])


def screen_content(text: str, *, source: str = "external_content") -> dict:
    """Classify untrusted content. Returns trust level + the NAMES
    of any injection patterns found. The content itself is data and
    may still be stored/processed as evidence (P-09 precedent) —
    what it can never do is instruct."""
    findings: list[str] = []
    for name, pattern in INJECTION_PATTERNS:
        if pattern.search(text or "") and name not in findings:
            findings.append(name)
    return {
        "source": source,
        "trust_level": trust_level_for_source(source),
        "trust_class": "untrusted_data",
        "injection_findings": findings,
        "instruction_shaped": bool(findings),
        "may_instruct": False,
    }


def screen_outbound(text: str) -> dict:
    """Stop secret-shaped values leaving in prompts/reports (§9.3).
    Returns pattern names only — the matched value is never echoed
    into the result, an event, or a log."""
    patterns = detect_secrets(text or "")
    return {"blocked": bool(patterns), "secret_patterns": patterns}


# ------------------------------------------------------------ handoffs (§14.4)
HANDOFF_REQUIRED_FIELDS = (
    "sender_id", "recipient_id", "task_id", "business_scope",
    "message_type", "content_classification", "evidence_refs",
    "requested_action", "permission_requirements",
)


def validate_handoff(envelope: dict) -> dict:
    """Validate a structured agent-to-agent handoff envelope.
    A handoff may REQUEST an action; it never transfers authority —
    the receiver must re-verify permissions through the broker, and
    a handoff asking to move owner-only permissions is refused
    outright (§14.4/§15.3)."""
    if not isinstance(envelope, dict):
        return {"valid": False, "missing": list(HANDOFF_REQUIRED_FIELDS),
                "reason": "handoff must be a structured object"}
    missing = [f for f in HANDOFF_REQUIRED_FIELDS
               if envelope.get(f) in (None, "")]
    if missing:
        return {"valid": False, "missing": missing,
                "reason": f"handoff is missing required fields: {missing}"}
    requested = [str(p) for p in envelope.get("permission_requirements") or []]
    from . import constants as C
    owner_only = [p for p in requested if p in C.OWNER_ONLY_PERMISSIONS]
    if owner_only:
        return {"valid": False, "missing": [],
                "reason": (f"handoff requests owner-only permissions {owner_only}; "
                           f"handoffs cannot transfer owner authority (§15.3)")}
    if envelope["sender_id"] == envelope["recipient_id"]:
        return {"valid": False, "missing": [],
                "reason": "a handoff to oneself is not a handoff"}
    return {"valid": True, "missing": [],
            "reason": ("envelope is structurally valid; the receiver must "
                       "independently verify permissions before acting (§14.4)")}
